from __future__ import annotations

import json
from pathlib import Path

from trove.domain.items import CONSUMPTION_LABELS, SOURCE_TYPE_LABELS
from trove.domain.search import document_tokens
from trove.web.schemas import (
    CollectionSchema,
    ErrorResponse,
    HealthResponse,
    LinkInspectResponse,
    ManifestResponse,
    MutationResponse,
    SearchResponse,
    SyncFileSchema,
    SyncStateResponse,
)

from .conftest import seed_item

CONTRACT = Path(__file__).resolve().parent.parent / "contract"


def _load(name: str) -> dict:
    return json.loads((CONTRACT / name).read_text(encoding="utf-8"))


def test_manifest_contract_fixture_matches_host_schema():
    manifest = ManifestResponse.model_validate(_load("manifest.json"))
    assert manifest.items[0].files[0].kind == "audio"
    assert manifest.items[0].tags == ["AI", "记忆"]
    assert manifest.tombstones[0].deleted_at > 0
    assert manifest.tombstones[0].epoch == manifest.epoch
    assert manifest.next_cursor == "42"
    assert manifest.epoch


def test_file_contract_fixture_matches_host_schema():
    file = SyncFileSchema.model_validate(_load("file.json"))
    assert file.kind == "transcript"
    assert file.mime == "application/json"
    assert len(file.sha256) == 64


def test_state_contract_fixture_matches_host_schema():
    state = SyncStateResponse.model_validate(_load("state.json"))
    assert state.items[0].consumption_state == "in_progress"
    assert state.items[1].book_locator is not None
    assert state.has_more is True


def test_search_contract_fixture_matches_host_schema():
    search = SearchResponse.model_validate(_load("search.json"))
    assert search.query
    assert search.count == 1
    item = search.results[0].item
    assert item.source_type_label == "Video"
    assert item.consumption_label == "In progress"
    assert item.processing_label == "Completed"
    assert item.audio_url and item.audio_url.endswith("/audio")
    assert item.cover_url and item.cover_url.endswith("/cover")
    assert item.has_cover is True
    assert {artifact.kind for artifact in item.artifacts} == {"audio", "cover"}
    for artifact in item.artifacts:
        assert artifact.url and artifact.url.endswith(f"/{artifact.kind}")
    evidence = search.results[0].evidence[0]
    assert evidence.doc_kind == "transcript"
    assert evidence.ref == "3:65000"
    assert evidence.url.endswith("/listen#segment-3")
    assert evidence.snippet
    assert search.results[0].item.tags == ["AI", "记忆"]


def test_mutation_contract_fixture_matches_host_schema():
    mutation = MutationResponse.model_validate(_load("mutation.json"))
    assert mutation.ok is True
    assert mutation.applied is False
    clock = mutation.field_clocks["tags"]
    assert clock.device_id == "device-1"
    assert clock.client_updated_at > 0
    assert mutation.warnings == ["sync.clock_skew"]
    assert mutation.item.version == 8


def test_health_contract_fixture_matches_host_schema():
    health = HealthResponse.model_validate(_load("health.json"))
    assert health.capabilities["sync"] is True
    assert health.capabilities["device_tokens"] is True
    assert health.capabilities["file_download"] is True
    assert health.database["fts5"] is True
    assert health.database["migration"]["head"] == "0007_stage_tasks"


def test_inspect_contract_fixture_matches_host_schema():
    inspect = LinkInspectResponse.model_validate(_load("inspect.json"))
    assert inspect.kind == "collection"
    assert inspect.episode_count == 2
    assert inspect.episodes[0].source_key.endswith("episode0001")
    assert inspect.total_duration_sec == 120.0


def test_collection_contract_fixture_matches_host_schema():
    collection = CollectionSchema.model_validate(_load("collection.json"))
    assert collection.episode_count == 2
    assert collection.status.queued == 2
    assert collection.items[0].collection_index == 1
    assert collection.items[1].title == "Episode Two"


def test_health_fixture_matches_live_migration_head(api_host):
    fixture = _load("health.json")
    live = api_host.client.get("/api/health").json()
    assert live["database"]["migration"]["head"] == fixture["database"]["migration"]["head"]
    assert live["capabilities"] == fixture["capabilities"]


def test_live_search_payload_keeps_fixture_labels_and_urls(api_host):
    bundle = seed_item(
        api_host,
        title="记忆与智能",
        source_type="video_url",
        platform="youtube",
        tags=["AI", "记忆"],
        consumption_state="in_progress",
    )
    api_host.runtime.search_index.index_item(bundle.item.id)
    api_host.login()
    payload = api_host.client.get("/api/search", params={"q": "记忆"}).json()
    item = payload["results"][0]["item"]
    assert item["source_type_label"] == SOURCE_TYPE_LABELS[item["source_type"]]
    assert item["consumption_label"] == CONSUMPTION_LABELS[item["consumption_state"]]
    assert item["processing_label"] == "Completed"
    assert item["audio_url"].endswith("/audio")
    for artifact in item["artifacts"]:
        if artifact["kind"] in {"audio", "cover"}:
            assert artifact["url"].endswith(f"/{artifact['kind']}")
        else:
            assert artifact["url"] is None


def test_search_query_contract_fixture_matches_host_tokenizer():
    fixture = _load("search-query.json")
    assert document_tokens(fixture["query"]) == fixture["tokens"]


def test_error_contract_fixture_matches_host_schema():
    error = ErrorResponse.model_validate(_load("error.json"))
    assert error.code == "auth.device_revoked"
    assert error.message
