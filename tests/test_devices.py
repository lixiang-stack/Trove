from __future__ import annotations

import json
import logging

from sqlalchemy import select

from trove.cli import main
from trove.db.models import DeviceToken

from .conftest import PASSWORD


def _device_token(host, name: str = "Pixel 9") -> dict:
    response = host.client.post(
        "/api/auth/device-token", json={"password": PASSWORD, "name": name}
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["device_id"]
    assert payload["token"]
    assert payload["name"] == name
    return payload


def test_password_exchanges_for_device_token_and_bearer_access(api_host):
    device = _device_token(api_host)
    client = api_host.client
    client.cookies.clear()

    response = client.get(
        "/api/items", headers={"authorization": f"Bearer {device['token']}"}
    )
    assert response.status_code == 200, response.text

    with api_host.runtime.sessions() as session:
        row = session.execute(
            select(DeviceToken).where(DeviceToken.device_id == device["device_id"])
        ).scalar_one()
        assert row.token_hash != device["token"]
        assert device["token"] not in row.token_hash
        assert len(row.token_hash) == 64


def test_wrong_password_is_rejected_and_rate_limited(api_host):
    for attempt in range(5):
        response = api_host.client.post(
            "/api/auth/device-token", json={"password": "wrong", "name": "Pixel"}
        )
        if attempt < 4:
            assert response.status_code == 401
            assert response.json()["code"] == "auth.invalid"
    assert response.status_code == 429


def test_revoked_token_is_rejected_immediately(api_host):
    device = _device_token(api_host)
    api_host.client.cookies.clear()
    headers = {"authorization": f"Bearer {device['token']}"}
    assert api_host.client.get("/api/items", headers=headers).status_code == 200

    revoked = api_host.client.delete(
        f"/api/devices/{device['device_id']}",
        headers={**headers, "origin": "http://evil.example"},
    )
    assert revoked.status_code == 204

    response = api_host.client.get("/api/items", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "auth.device_revoked"


def test_password_change_invalidates_all_device_tokens(api_host):
    first = _device_token(api_host, "First")
    second = _device_token(api_host, "Second")
    api_host.client.cookies.clear()
    for device in (first, second):
        response = api_host.client.get(
            "/api/items", headers={"authorization": f"Bearer {device['token']}"}
        )
        assert response.status_code == 200

    api_host.config.set_password("rotated-password")

    for device in (first, second):
        response = api_host.client.get(
            "/api/items", headers={"authorization": f"Bearer {device['token']}"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "auth.device_revoked"


def test_unknown_bearer_token_is_reported_separately(api_host):
    response = api_host.client.get(
        "/api/items", headers={"authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "auth.device_token_invalid"


def test_bearer_writes_skip_csrf_but_cookie_writes_do_not(api_host):
    device = _device_token(api_host)
    api_host.client.cookies.clear()
    response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://example.com/watch?v=abc"},
        headers={
            "authorization": f"Bearer {device['token']}",
            "sec-fetch-site": "cross-site",
        },
    )
    assert response.status_code in {200, 201, 422}, response.text
    assert response.status_code != 403

    api_host.login()
    cookie_response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://example.com/watch?v=abc"},
        headers={"sec-fetch-site": "cross-site"},
    )
    assert cookie_response.status_code == 403


def test_cookie_session_still_works_and_devices_are_listed(api_host):
    device = _device_token(api_host)
    api_host.login()
    response = api_host.client.get("/api/devices")
    assert response.status_code == 200
    devices = response.json()["devices"]
    assert [row["device_id"] for row in devices] == [device["device_id"]]
    assert "token" not in devices[0]
    assert "token_hash" not in devices[0]


def test_device_cli_lists_and_revokes(api_host, capsys):
    device = _device_token(api_host)
    home = str(api_host.config.home)

    assert main(["--home", home, "device", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["devices"][0]["device_id"] == device["device_id"]

    assert main(["--home", home, "device", "revoke", device["device_id"]]) == 0
    capsys.readouterr()
    assert main(["--home", home, "device", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["devices"][0]["revoked_at"] is not None


def test_token_never_appears_in_logs(api_host, caplog):
    with caplog.at_level(logging.INFO):
        device = _device_token(api_host)
        api_host.client.cookies.clear()
        api_host.client.get(
            "/api/items", headers={"authorization": f"Bearer {device['token']}"}
        )
    assert device["token"] not in caplog.text
    assert "authorization" not in caplog.text.lower()


def test_last_used_at_is_throttled(api_host, monkeypatch):
    device = _device_token(api_host)
    with api_host.runtime.sessions() as session:
        row = session.execute(
            select(DeviceToken).where(DeviceToken.device_id == device["device_id"])
        ).scalar_one()
        first_seen = row.last_used_at

    monkeypatch.setattr("trove.services.devices.utc_ms", lambda: first_seen + 1000)
    api_host.client.cookies.clear()
    api_host.client.get(
        "/api/items", headers={"authorization": f"Bearer {device['token']}"}
    )
    with api_host.runtime.sessions() as session:
        row = session.execute(
            select(DeviceToken).where(DeviceToken.device_id == device["device_id"])
        ).scalar_one()
        assert row.last_used_at == first_seen

    monkeypatch.setattr("trove.services.devices.utc_ms", lambda: first_seen + 6 * 60 * 1000)
    api_host.client.get(
        "/api/items", headers={"authorization": f"Bearer {device['token']}"}
    )
    with api_host.runtime.sessions() as session:
        row = session.execute(
            select(DeviceToken).where(DeviceToken.device_id == device["device_id"])
        ).scalar_one()
        assert row.last_used_at == first_seen + 6 * 60 * 1000
