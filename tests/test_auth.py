from __future__ import annotations

from trove.services.auth import is_secure_request

from .conftest import PASSWORD


def test_unauthenticated_api_is_401_and_html_redirects(api_host):
    response = api_host.client.get("/api/items")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.required"
    response = api_host.client.get("/library")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_login_wrong_password_is_generic(api_host):
    response = api_host.client.post("/login", data={"password": "nope"})
    assert response.status_code == 401
    assert "Incorrect password" in response.text
    assert "not found" not in response.text.lower()


def test_login_logout_and_session_persistence(host_factory):
    first = host_factory(start_worker=False, home_name="persisted")
    first.login()
    assert first.client.get("/library").status_code == 200
    token = first.client.cookies.get("trove_session")
    assert token
    second = host_factory(
        start_worker=False, home_name="persisted", configure_password=False
    )
    second.client.cookies.set("trove_session", token)
    assert second.client.get("/library").status_code == 200
    second.client.post("/logout")
    assert second.client.get("/library").status_code == 303
    fresh = host_factory(
        start_worker=False, home_name="persisted", configure_password=False
    )
    fresh.client.cookies.set("trove_session", token)
    assert fresh.client.get("/library").status_code == 303


def test_password_change_invalidates_existing_sessions(host_factory):
    host = host_factory(start_worker=False, home_name="password-rotation")
    host.login(PASSWORD)
    token = host.client.cookies.get("trove_session")
    assert token

    host.config.set_password("new-password")

    assert host.client.get("/library").status_code == 303

    old_login = host.client.post("/login", data={"password": PASSWORD})
    assert old_login.status_code == 401
    new_login = host.client.post("/login", data={"password": "new-password"})
    assert new_login.status_code == 303
    assert host.client.get("/library").status_code == 200


def test_session_cookie_is_signed_and_secret_persists(api_host):
    api_host.login()
    token = api_host.client.cookies.get("trove_session")
    assert token and "." in token
    assert api_host.config.session_secret not in token
    secret = api_host.config.session_secret
    api_host.config.ensure_layout()
    assert api_host.config.session_secret == secret


def test_login_rate_limit(api_host):
    for _ in range(5):
        response = api_host.client.post("/login", data={"password": "wrong"})
    assert response.status_code == 429
    assert response.headers["retry-after"]


def test_success_resets_login_failures(host_factory):
    other = host_factory(start_worker=False, home_name="reset")
    for _ in range(4):
        other.client.post("/login", data={"password": "wrong"})
    other.login()
    for _ in range(4):
        response = other.client.post("/login", data={"password": "wrong"})
    assert response.status_code == 401


def test_csrf_origin_is_enforced(api_host):
    api_host.login()
    response = api_host.client.post(
        "/items/does-not-exist/delete", headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403
    response = api_host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://example.com"},
        headers={"sec-fetch-site": "cross-site"},
    )
    assert response.status_code == 403


def test_secure_cookie_only_under_https(tmp_path):
    from trove.config import Config

    config = Config(home=tmp_path / "Trove")
    assert is_secure_request("https", None, config) is True
    assert is_secure_request("http", "https", config) is True
    assert is_secure_request("http", None, config) is False


def test_password_hash_not_plaintext(api_host):
    config_text = api_host.config.config_path.read_text(encoding="utf-8")
    assert PASSWORD not in config_text
    assert "argon2id" in config_text
