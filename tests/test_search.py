from __future__ import annotations

from sqlalchemy import text

from trove.db.models import BookChapter, BookParagraph, TranscriptSegment

from .conftest import seed_item


def _add_segments(host, item_id: str, *texts: str) -> None:
    with host.runtime.sessions() as session:
        session.add_all(
            [
                TranscriptSegment(
                    item_id=item_id,
                    seq=index,
                    start_ms=index * 1000,
                    end_ms=(index + 1) * 1000,
                    text=value,
                )
                for index, value in enumerate(texts)
            ]
        )
        session.commit()


def _add_book_paragraphs(host, item_id: str, *texts: str) -> None:
    with host.runtime.sessions() as session:
        session.add_all(
            [
                BookParagraph(
                    item_id=item_id,
                    chapter_index=0,
                    paragraph_index=index,
                    text=value,
                )
                for index, value in enumerate(texts)
            ]
        )
        session.commit()


def _index(host, item_id: str) -> None:
    host.runtime.search_index.index_item(item_id)


def test_search_matches_title_summary_tag_transcript_and_book(host):
    item = seed_item(
        host,
        title="Zephyr Quartz",
        summary="Nimbus summary",
        tags=["Solstice"],
    )
    _add_segments(host, item.item.id, "delta transcript")
    _add_book_paragraphs(host, item.item.id, "epsilon book")
    _index(host, item.item.id)
    host.login()

    for query, kind in (
        ("zephyr", "title"),
        ("nimbus", "summary"),
        ("solstice", "tag"),
        ("delta", "transcript"),
        ("epsilon", "book"),
    ):
        payload = host.client.get("/api/search", params={"q": query}).json()
        assert payload["count"] == 1, query
        assert payload["results"][0]["item"]["id"] == item.item.id
        assert payload["results"][0]["evidence"][0]["doc_kind"] == kind


def test_search_uses_porter_stems_for_english(host):
    item = seed_item(host, title="Stemming")
    _add_segments(host, item.item.id, "he runs daily")
    _index(host, item.item.id)
    host.login()

    payload = host.client.get("/api/search", params={"q": "running"}).json()

    assert payload["count"] == 1
    assert payload["results"][0]["item"]["id"] == item.item.id


def test_search_aggregates_by_item_with_at_most_three_evidence_rows(host):
    item = seed_item(host, title="聚合条目", summary="智能摘要", tags=["智能体"])
    _add_segments(
        host,
        item.item.id,
        "智能第一段",
        "智能第二段",
        "智能第三段",
        "智能第四段",
        "智能第五段",
    )
    _add_book_paragraphs(host, item.item.id, "智能书段落")
    _index(host, item.item.id)
    other = seed_item(host, title="无关条目", source_key="seed:search-other")
    _index(host, other.item.id)
    host.login()

    payload = host.client.get("/api/search", params={"q": "智能"}).json()

    assert payload["count"] == 1
    result = payload["results"][0]
    assert result["item"]["id"] == item.item.id
    evidence = result["evidence"]
    assert 1 <= len(evidence) <= 3
    assert len({entry["ref"] for entry in evidence}) == len(evidence)
    for entry in evidence:
        assert entry["doc_kind"] in {"title", "summary", "tag", "transcript", "book"}
        assert "智能" in entry["text"]
        assert "智能" in entry["snippet"]
        assert entry["ref"]


def test_chinese_phrase_and_two_character_queries_hit(host):
    item = seed_item(host, title="人工智能导论")
    _add_segments(host, item.item.id, "智能体需要记忆，也需要遗忘。")
    host.login()
    _index(host, item.item.id)

    phrase = host.client.get("/api/search", params={"q": "人工智能"}).json()
    two_chars = host.client.get("/api/search", params={"q": "记忆"}).json()
    single = host.client.get("/api/search", params={"q": "忘"}).json()

    assert phrase["count"] == 1
    assert two_chars["count"] == 1
    assert single["count"] == 1


def test_mixed_single_character_query_requires_all_terms(host):
    only_char = seed_item(host, title="智", source_key="seed:only-char")
    mixed = seed_item(host, title="AI 智能", source_key="seed:mixed-char")
    _index(host, only_char.item.id)
    _index(host, mixed.item.id)
    host.login()

    payload = host.client.get("/api/search", params={"q": "AI 智"}).json()

    assert payload["count"] == 1
    assert payload["results"][0]["item"]["id"] == mixed.item.id


def test_repeated_cjk_phrase_still_matches(host):
    item = seed_item(host, title="记忆记忆")
    host.login()
    _index(host, item.item.id)

    payload = host.client.get("/api/search", params={"q": "记忆记忆"}).json()

    assert payload["count"] == 1


def test_search_filters_combine_like_library(host):
    alpha = seed_item(
        host,
        title="Common Alpha",
        source_key="seed:filter-alpha",
        source_type="video_url",
        platform="youtube",
        consumption_state="in_progress",
        tags=["记忆"],
        summary="",
    )
    beta = seed_item(
        host,
        title="Common Beta",
        source_key="seed:filter-beta",
        source_type="local_audio",
        platform="local",
        consumption_state="unstarted",
        tags=["其他"],
    )
    _add_segments(host, alpha.item.id, "shared keyword alpha")
    _add_segments(host, beta.item.id, "shared keyword beta")
    for item_id in (alpha.item.id, beta.item.id):
        _index(host, item_id)
    host.login()

    def search(**params):
        response = host.client.get("/api/search", params={"q": "shared", **params})
        assert response.status_code == 200, response.text
        return {result["item"]["id"] for result in response.json()["results"]}

    assert search() == {alpha.item.id, beta.item.id}
    assert search(type="video_url") == {alpha.item.id}
    assert search(consumption="in_progress") == {alpha.item.id}
    assert search(tag="记忆") == {alpha.item.id}
    assert search(source="youtube") == {alpha.item.id}
    assert search(
        type="video_url", consumption="in_progress", tag="记忆", source="youtube"
    ) == {alpha.item.id}
    assert search(tag="不存在") == set()


def test_search_and_library_filter_ui_share_semantics(host):
    alpha = seed_item(
        host,
        title="UI Alpha",
        source_key="seed:ui-alpha",
        source_type="video_url",
        platform="youtube",
        consumption_state="in_progress",
        tags=["记忆"],
    )
    beta = seed_item(
        host,
        title="UI Beta",
        source_key="seed:ui-beta",
        source_type="local_audio",
        platform="local",
        tags=["其他"],
    )
    _add_segments(host, alpha.item.id, "shared ui keyword")
    _add_segments(host, beta.item.id, "shared ui keyword")
    for item_id in (alpha.item.id, beta.item.id):
        _index(host, item_id)
    host.login()

    params = {
        "q": "shared",
        "type": "video_url",
        "consumption": "in_progress",
        "tag": "记忆",
        "source": "youtube",
    }
    search_page = host.client.get("/search", params=params)
    library_page = host.client.get("/library", params=params)
    assert search_page.status_code == 200
    assert library_page.status_code == 200
    assert "UI Alpha" in search_page.text and "UI Beta" not in search_page.text
    assert "UI Alpha" in library_page.text and "UI Beta" not in library_page.text
    assert "清空过滤" in search_page.text

    unfiltered = host.client.get("/search", params={"q": "shared"})
    assert "UI Alpha" in unfiltered.text and "UI Beta" in unfiltered.text
    assert "类型" in unfiltered.text and "来源" in unfiltered.text

    too_long = host.client.get("/search", params={"q": "a" * 201})
    assert too_long.status_code == 200
    assert "查询过长" in too_long.text
    empty = host.client.get("/search", params={"q": "zzzz-not-found"})
    assert "没有命中" in empty.text


def test_index_reads_content_package_and_rebuilds_without_db_text(host):
    item = seed_item(host, title="Package Source")
    host.runtime.package.write_json(
        item.item.id,
        "transcript.json",
        {
            "language": "zh",
            "segments": [
                {"seq": 0, "start_ms": 0, "end_ms": 1000, "text": "包内独有词组"},
            ],
        },
    )
    host.runtime.package.write_json(
        item.item.id,
        "book.json",
        {
            "title": "Package Source",
            "chapters": [
                {
                    "chapter_index": 0,
                    "title": "第一章",
                    "text": "包内书页",
                    "paragraphs": ["包内书页"],
                }
            ],
        },
    )
    host.login()
    _index(host, item.item.id)

    assert host.client.get("/api/search", params={"q": "包内独有"}).json()["count"] == 1
    assert host.client.get("/api/search", params={"q": "包内书页"}).json()["count"] == 1
    with host.runtime.sessions() as session:
        assert session.execute(text("SELECT count(*) FROM transcript_segments")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM book_paragraphs")).scalar() == 0
    host.runtime.search_index.rebuild()
    assert host.client.get("/api/search", params={"q": "包内独有"}).json()["count"] == 1
    assert host.client.get("/api/search", params={"q": "包内书页"}).json()["count"] == 1


def test_index_rebuild_is_idempotent_and_preserves_results(host, monkeypatch):
    first = seed_item(host, title="Rebuild Alpha")
    second = seed_item(host, title="Rebuild Beta", source_key="seed:rebuild-beta")
    _add_segments(host, first.item.id, "稳定重建记忆")
    for item_id in (first.item.id, second.item.id):
        _index(host, item_id)
    host.login()

    before = host.client.get("/api/search", params={"q": "重建"}).json()
    assert before["count"] == 1
    assert host.runtime.search_index.rebuild() == 2
    after = host.client.get("/api/search", params={"q": "重建"}).json()
    assert after == before
    assert host.runtime.search_index.rebuild() == 2
    assert host.client.get("/api/search", params={"q": "重建"}).json() == before

    monkeypatch.setenv("TROVE_HOME", str(host.config.home))
    from trove.cli import main

    assert main(["index", "rebuild"]) == 0
    assert host.client.get("/api/search", params={"q": "重建"}).json() == before


def test_search_query_limits_and_fts_syntax_are_safe(host):
    item = seed_item(host, title="Safe Search")
    _index(host, item.item.id)
    host.login()

    long_query = host.client.get("/api/search", params={"q": "a" * 201})
    injection = host.client.get("/api/search", params={"q": '" AND ( OR'})

    assert long_query.status_code == 422
    assert long_query.json()["code"] == "request.invalid"
    assert injection.status_code == 200


def test_book_title_result_falls_back_to_reader(host):
    item = seed_item(
        host,
        title="Book Title Only",
        source_type="epub",
        with_audio=False,
        run_state=None,
    )
    _index(host, item.item.id)
    host.login()

    payload = host.client.get("/api/search", params={"q": "Book Title"}).json()

    assert payload["results"][0]["evidence"][0]["url"] == f"/items/{item.item.id}/read"


def test_book_search_result_links_to_paragraph_anchor(host):
    item = seed_item(
        host,
        title="Book Locate",
        source_type="epub",
        with_audio=False,
        run_state=None,
    )
    with host.runtime.sessions() as session:
        session.add(
            BookChapter(
                item_id=item.item.id,
                chapter_index=0,
                title="第一章",
                html="<p>bookword 在这里</p>",
                text="bookword 在这里",
            )
        )
        session.add(
            BookParagraph(
                item_id=item.item.id,
                chapter_index=0,
                paragraph_index=0,
                text="bookword 在这里",
            )
        )
        session.commit()
    _index(host, item.item.id)
    host.login()

    payload = host.client.get("/api/search", params={"q": "bookword"}).json()
    url = payload["results"][0]["evidence"][0]["url"]
    assert url == f"/items/{item.item.id}/read#paragraph-0-0"
    page = host.client.get(url.split("#", 1)[0])
    assert page.status_code == 200
    assert 'id="paragraph-0-0"' in page.text
    assert "bookword 在这里" in page.text


def test_search_evidence_refs_point_to_transcript_and_book_units(host):
    item = seed_item(host, title="Refs")
    _add_segments(host, item.item.id, "引用定位记忆")
    _add_book_paragraphs(host, item.item.id, "引用定位书")
    _index(host, item.item.id)
    host.login()

    transcript = host.client.get("/api/search", params={"q": "引用定位记忆"}).json()
    book = host.client.get("/api/search", params={"q": "引用定位书"}).json()

    assert transcript["results"][0]["evidence"][0]["ref"] == "0:0"
    assert book["results"][0]["evidence"][0]["ref"] == "0:0"
    with host.runtime.sessions() as session:
        assert session.execute(text("SELECT count(*) FROM search_fts")).scalar() > 0
