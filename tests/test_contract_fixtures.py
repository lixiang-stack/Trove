from __future__ import annotations

import json
from pathlib import Path

from trove.domain.search import document_tokens
from trove.web.schemas import (
    ErrorResponse,
    ManifestResponse,
    SearchResponse,
    SyncFileSchema,
    SyncStateResponse,
)

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
    evidence = search.results[0].evidence[0]
    assert evidence.doc_kind == "transcript"
    assert evidence.ref == "3:65000"
    assert evidence.snippet
    assert search.results[0].item.tags == ["AI", "记忆"]


def test_search_query_contract_fixture_matches_host_tokenizer():
    fixture = _load("search-query.json")
    assert document_tokens(fixture["query"]) == fixture["tokens"]


def test_error_contract_fixture_matches_host_schema():
    error = ErrorResponse.model_validate(_load("error.json"))
    assert error.code == "auth.device_revoked"
    assert error.message
