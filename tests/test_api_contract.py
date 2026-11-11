from __future__ import annotations

import json

import pytest

from .conftest import seed_item

SPEC_PATHS = {
    "/api/items",
    "/api/items/{item_id}",
    "/api/items/{item_id}/audio",
    "/api/items/{item_id}/transcript",
    "/api/items/{item_id}/book/chapters/{chapter_index}",
    "/api/items/{item_id}/progress",
    "/api/items/{item_id}/retry",
    "/api/items/{item_id}/reprocess",
    "/api/items/{item_id}/cancel",
    "/api/items/{item_id}/tags/{tag}",
    "/api/runs/{run_id}",
    "/api/runs/{run_id}/cancel",
    "/api/search",
    "/api/tags",
    "/api/continue",
    "/api/export",
    "/api/uploads",
    "/api/feeds/preview",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/health",
}


def test_openapi_covers_mvp_endpoints_and_security(api_host):
    response = api_host.client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    paths = set(schema["paths"])
    assert paths >= SPEC_PATHS
    assert schema["components"]["securitySchemes"]["cookieAuth"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "trove_session",
    }
    assert schema["paths"]["/api/items"]["get"]["security"] == [{"cookieAuth": []}]
    assert "security" not in schema["paths"]["/api/auth/login"]["post"]
    assert "security" not in schema["paths"]["/api/health"]["get"]

    item_schema = schema["components"]["schemas"]["ItemSchema"]["properties"]
    assert "artifacts" in item_schema
    assert "source_path" not in item_schema
    assert "sha256" in schema["components"]["schemas"]["ArtifactSchema"]["properties"]

    response_schema = schema["paths"]["/api/items/{item_id}"]["get"]["responses"]["200"]
    assert response_schema["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ItemSchema"
    )
    error_schema = schema["paths"]["/api/items"]["get"]["responses"]["401"]
    assert error_schema["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )


def test_error_shape_is_stable(api_host):
    unauthorized = api_host.client.get("/api/items")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "auth.required"
    assert unauthorized.json()["message"]

    api_host.login()
    missing = api_host.client.get("/api/items/missing")
    assert missing.status_code == 404
    assert missing.json()["code"] == "item.not_found"

    missing_run = api_host.client.get("/api/runs/missing")
    assert missing_run.status_code == 404
    assert missing_run.json()["code"] == "run.not_found"

    invalid = api_host.client.post("/api/items", json={"kind": "url"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "request.invalid"

    invalid_json = api_host.client.patch("/api/items/missing", json={"title": 1})
    assert invalid_json.status_code == 422
    assert invalid_json.json()["code"] == "request.invalid"
    assert invalid_json.json()["details"]["errors"]


def test_run_payload_does_not_leak_home_paths(host):
    from trove.logging_setup import append_run_log

    original_path = str(host.config.home / "outside-home-source.m4a")
    bundle = seed_item(
        host,
        title="Path redaction",
        source_path=original_path,
        run_state="failed",
    )
    assert bundle.run is not None
    append_run_log(
        host.config,
        bundle.run.id,
        f"failed at {host.config.home}/library/{bundle.item.id}/audio.m4a "
        f"and {original_path}",
        level="error",
    )
    host.login()
    run = host.client.get(f"/api/items/{bundle.item.id}").json()["run"]
    assert str(host.config.home) not in json.dumps(run)
    assert original_path not in json.dumps(run)
    assert "~/library/" in run["log_tail"][-1]
    assert "<local-source>" in run["log_tail"][-1]


def test_duplicate_add_returns_existing_item(api_host):
    api_host.login()
    payload = {"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    first = api_host.client.post("/api/items", json=payload)
    assert first.status_code == 201
    second = api_host.client.post("/api/items", json=payload)
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["item"]["id"] == first.json()["item"]["id"]


def test_login_rate_limit_uses_stable_error(api_host):
    for _ in range(5):
        response = api_host.client.post("/api/auth/login", json={"password": "wrong"})
    assert response.status_code == 429
    assert response.json()["code"] == "auth.rate_limited"
    assert response.headers["retry-after"].isdigit()


def test_item_list_pagination_and_filters(host):
    for title, tag, source_type in (
        ("Alpha", "记忆", "video_url"),
        ("Beta", "智能体", "local_audio"),
        ("Gamma", "记忆", "local_audio"),
    ):
        seed_item(
            host,
            title=title,
            tags=[tag],
            source_type=source_type,
            platform="youtube" if source_type == "video_url" else "local",
        )
    host.login()

    first = host.client.get("/api/items", params={"limit": 2}).json()
    second = host.client.get("/api/items", params={"limit": 2, "offset": 2}).json()
    assert first["total"] == 3
    assert first["count"] == 2
    assert second["count"] == 1
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )

    filtered = host.client.get(
        "/api/items", params={"type": "local_audio", "tag": "记忆", "source": "local"}
    ).json()
    assert [item["title"] for item in filtered["items"]] == ["Gamma"]

    consumed = host.client.get("/api/items", params={"sort": "recent_consumed"}).json()
    assert consumed["total"] == 3

    failed = seed_item(host, title="Failed", run_state="failed")
    inbox = host.client.get("/api/items", params={"state": "failed"}).json()
    assert [item["id"] for item in inbox["items"]] == [failed.item.id]


def test_continue_search_tags_and_artifacts_are_available_over_api(host):
    listening = seed_item(
        host,
        title="继续听",
        consumption_state="in_progress",
        position=5.0,
        tags=["记忆"],
    )
    seed_item(host, title="未开始", source_key="seed:unstarted")
    host.runtime.search_index.index_item(listening.item.id)
    host.login()

    continue_payload = host.client.get("/api/continue").json()
    assert continue_payload["entries"][0]["item"]["id"] == listening.item.id
    assert continue_payload["entries"][0]["kind"] == "listen"
    assert continue_payload["entries"][0]["url"].endswith("/listen")

    search = host.client.get("/api/search", params={"q": "继续"}).json()
    assert search["count"] == 1
    assert search["results"][0]["evidence"][0]["doc_kind"] == "title"

    tags = host.client.get("/api/tags").json()
    assert tags == {"tags": [{"name": "记忆", "count": 1}]}

    detail = host.client.get(f"/api/items/{listening.item.id}").json()
    assert detail["artifacts"][0]["sha256"]
    assert detail["artifacts"][0]["url"].endswith("/audio")
    assert "source_path" not in detail
    assert str(host.config.home) not in str(detail)


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"range": "bytes=0-9"}, 206),
        ({"range": "bytes=999999-"}, 416),
    ],
)
def test_media_range_contract(host, headers, expected):
    bundle = seed_item(host, title="Range contract")
    host.login()
    response = host.client.get(f"/api/items/{bundle.item.id}/audio", headers=headers)
    assert response.status_code == expected
    if expected == 206:
        assert response.headers["etag"].startswith('"')
        assert response.headers["accept-ranges"] == "bytes"
