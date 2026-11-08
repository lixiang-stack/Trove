from __future__ import annotations

import pytest

from .conftest import seed_item
from .fakes import FIXTURES, wait_until

pytestmark = pytest.mark.browser


@pytest.fixture
def browser():
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch(
                headless=True,
                channel="chrome",
                args=["--autoplay-policy=no-user-gesture-required"],
            )
        except Error as exc:
            pytest.skip(f"Chrome is not available for Playwright: {exc}")
        yield instance
        instance.close()


def _context(browser, host):
    host.login()
    token = host.client.cookies.get("trove_session")
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_cookies(
        [{"name": "trove_session", "value": token, "url": host.base_url}]
    )
    return context


def _seed_transcript(host, item_id: str) -> None:
    from trove.db.models import TranscriptSegment

    with host.runtime.sessions() as session:
        session.add_all(
            [
                TranscriptSegment(
                    item_id=item_id,
                    seq=0,
                    start_ms=0,
                    end_ms=4000,
                    text="今天想聊一个我最近反复想到的问题：为什么智能体的瓶颈不是模型，而是记忆。",
                ),
                TranscriptSegment(
                    item_id=item_id,
                    seq=1,
                    start_ms=4000,
                    end_ms=9000,
                    text="我们总把上下文窗口当成记忆，但上下文是临时的。",
                ),
            ]
        )
        session.commit()


def test_playback_navigation_inline_and_transcript(host, browser):
    bundle = seed_item(
        host,
        title="浏览器播放测试",
        author="作者",
        tags=["记忆"],
        duration=20.0,
        audio_fixture="long.m4a",
    )
    _seed_transcript(host, bundle.item.id)
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    page.wait_for_selector(f'[data-inline-for="{bundle.item.id}"]', state="attached")
    page.click(f'[data-play-item][data-item-id="{bundle.item.id}"]')
    page.wait_for_function(
        "() => { const a = document.querySelector('#global-audio');"
        " return a && !a.paused && a.currentTime > 0.05; }",
        timeout=10000,
    )
    assert page.url.endswith("/library")
    assert page.locator(f'[data-inline-for="{bundle.item.id}"]').is_visible()
    assert page.evaluate("window.TrovePlayer.state.playing") is True
    metadata_title = page.evaluate(
        "() => navigator.mediaSession && navigator.mediaSession.metadata"
        " ? navigator.mediaSession.metadata.title : null"
    )
    assert metadata_title == "浏览器播放测试"

    page.click(".queue-body")
    page.wait_for_url("**/listen")
    page.wait_for_selector(".now-playing")
    first_time = page.evaluate("document.querySelector('#global-audio').currentTime")
    assert page.evaluate("window.TrovePlayer.state.playing") is True
    assert page.evaluate("document.querySelector('#global-audio').currentTime") >= first_time

    details = page.locator("details.now-transcript")
    assert details.get_attribute("open") is None
    details.locator("summary").click()
    assert details.get_attribute("open") is not None
    assert page.evaluate("window.TrovePlayer.state.playing") is True
    details.locator("summary").click()
    assert details.get_attribute("open") is None

    page.click(".now-back")
    page.wait_for_url("**/library")
    assert page.evaluate("window.TrovePlayer.state.playing") is True
    assert page.evaluate("document.querySelector('#global-audio').currentTime") > 0
    assert page.locator(f'[data-inline-for="{bundle.item.id}"]').is_visible()

    page.wait_for_function(
        "() => document.querySelector('#global-audio').currentTime > 1.2",
        timeout=10000,
    )
    page.evaluate("document.querySelector('#global-audio').pause()")
    wait_until(
        lambda: host.item(bundle.item.id)["audio_position_sec"] > 0,
        timeout=5,
    )
    payload = host.item(bundle.item.id)
    assert payload["consumption_state"] == "in_progress"
    context.close()


def test_direct_listen_restores_progress_and_mobile_layout(host, browser):
    bundle = seed_item(
        host,
        title="续听测试",
        consumption_state="in_progress",
        position=5.0,
        duration=20.0,
        audio_fixture="long.m4a",
    )
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/items/{bundle.item.id}/listen", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => { const a = document.querySelector('#global-audio');"
        " return a && a.readyState >= 1 && a.currentTime >= 4.5; }",
        timeout=10000,
    )
    assert page.locator("#mini-player").is_visible() is False
    assert page.locator(".bottom-nav").is_visible() is False
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    assert page.locator(".bottom-nav").is_visible() is True
    assert page.locator(".queue-item").first.is_visible()
    context.close()


def test_manual_finish_updates_consumption_state(host, browser):
    bundle = seed_item(
        host,
        title="手动完成",
        duration=20.0,
        audio_fixture="long.m4a",
    )
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/items/{bundle.item.id}/listen", wait_until="domcontentloaded")
    page.wait_for_selector(".now-playing")
    page.click('[data-player-action="finish"]')
    wait_until(
        lambda: host.item(bundle.item.id)["consumption_state"] == "finished",
        timeout=5,
    )
    context.close()


def test_empty_library_mobile_has_add_call_to_action(host, browser):
    context = _context(browser, host)
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    assert page.get_by_text("Library 还是空的").is_visible()
    link = page.get_by_role("button", name="添加第一条内容")
    assert link.is_visible()
    link.click()
    page.wait_for_url("**/add")
    assert page.get_by_text("添加内容").first.is_visible()
    context.close()


def test_status_updates_and_polling_stops(host_factory, browser):
    host = host_factory(start_worker=False, home_name="browser-status")
    host.login()
    response = host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    item_id = response.json()["item"]["id"]
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    badge = page.locator(f'[data-item-id="{item_id}"] .badge').first
    assert "排队中" in badge.inner_text()
    assert badge.get_attribute("hx-trigger") == "every 3s"
    from trove.worker import WorkerThread

    worker = WorkerThread(host.runtime).start()
    try:
        page.wait_for_function(
            """(itemId) => {
                const row = document.querySelector(`[data-item-id="${itemId}"]`);
                const badge = row && row.querySelector('.badge');
                return badge && badge.textContent.includes('已完成');
            }""",
            arg=item_id,
            timeout=20000,
        )
    finally:
        worker.stop()
    badge = page.locator(f'[data-item-id="{item_id}"] .badge').first
    assert badge.get_attribute("hx-trigger") is None
    context.close()


def test_login_page_and_upload_flow(host, browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(f"{host.base_url}/login", wait_until="domcontentloaded")
    page.fill('input[name="password"]', "test-password")
    page.click('button[type="submit"]')
    page.wait_for_url("**/library")
    page.goto(f"{host.base_url}/add", wait_until="domcontentloaded")
    page.set_input_files("#upload-input", str(FIXTURES / "short.wav"))
    page.click('#upload-form button[type="submit"]')
    page.wait_for_url("**/items/*", timeout=15000)
    page.wait_for_selector(".detail-page")
    assert "short" in page.locator(".detail-title h1").inner_text()
    context.close()


def test_speed_and_seek_controls(host, browser):
    bundle = seed_item(host, title="控件测试", duration=20.0, audio_fixture="long.m4a")
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    page.click(f'[data-play-item][data-item-id="{bundle.item.id}"]')
    page.wait_for_function(
        "() => { const a = document.querySelector('#global-audio');"
        " return a && !a.paused && a.currentTime > 0.05; }",
        timeout=10000,
    )
    page.click('[data-player-action="speed"]')
    assert page.evaluate("window.TrovePlayer.state.speed") == 1.25
    assert page.evaluate("document.querySelector('#global-audio').playbackRate") == 1.25
    page.evaluate(
        """() => {
            const input = document.querySelector('[data-player-seek]');
            input.value = '500';
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }"""
    )
    assert page.evaluate("document.querySelector('#global-audio').currentTime") > 5
    context.close()


def test_mobile_now_playing_layout(host, browser):
    bundle = seed_item(host, title="手机播放页", duration=20.0, audio_fixture="long.m4a")
    context = _context(browser, host)
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{host.base_url}/items/{bundle.item.id}/listen", wait_until="domcontentloaded")
    assert page.locator(".now-playing").is_visible()
    assert page.locator(".now-controls").is_visible()
    context.close()
