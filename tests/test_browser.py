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


def test_nav_active_state_follows_htmx_navigation(host, browser):
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    assert page.locator(".main-nav a.active").get_attribute("href") == "/library"
    page.click('.main-nav a[href="/search"]')
    page.wait_for_url("**/search")
    assert page.locator(".main-nav a.active").get_attribute("href") == "/search"
    page.click('.main-nav a[href="/add"]')
    page.wait_for_url("**/add")
    assert page.locator(".main-nav a.active").get_attribute("href") == "/add"
    page.click('.main-nav a[href="/library"]')
    page.wait_for_url("**/library")
    assert page.locator(".main-nav a.active").get_attribute("href") == "/library"
    page.set_viewport_size({"width": 390, "height": 844})
    page.click('.bottom-nav a[href="/search"]')
    page.wait_for_url("**/search")
    assert page.locator(".bottom-nav a.active").get_attribute("href") == "/search"
    context.close()


def test_search_input_is_usable(host, browser):
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/search", wait_until="domcontentloaded")
    field = page.locator('input[name="q"]')
    box = field.bounding_box()
    assert box is not None and box["width"] > 200
    field.fill("记忆")
    assert field.input_value() == "记忆"
    context.close()


def test_light_theme_is_forced_in_dark_system(host, browser):
    bundle = seed_item(host, title="深色系统下的可读性", author="作者")
    host.login()
    token = host.client.cookies.get("trove_session")
    context = browser.new_context(
        viewport={"width": 1280, "height": 900}, color_scheme="dark"
    )
    context.add_cookies(
        [{"name": "trove_session", "value": token, "url": host.base_url}]
    )
    page = context.new_page()
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    row = page.locator(f'.queue-item[data-item-id="{bundle.item.id}"]')
    colors = row.evaluate(
        "(e) => { const s = getComputedStyle(e);"
        " return { background: s.backgroundColor, color: s.color }; }"
    )
    assert colors["color"] == "rgb(31, 29, 26)"
    page.goto(f"{host.base_url}/add", wait_until="domcontentloaded")
    heading = page.locator("h1").evaluate(
        "(e) => { const s = getComputedStyle(e); return s.color; }"
    )
    assert heading == "rgb(31, 29, 26)"
    context.close()


def test_listen_page_is_readable_in_dark_system(host_factory, browser):
    host = host_factory(start_worker=False, home_name="browser-listen-dark")
    host.login()
    response = host.client.post(
        "/api/items",
        json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    item_id = response.json()["item"]["id"]
    from sqlalchemy import text

    with host.runtime.sessions() as session:
        session.execute(
            text(
                "UPDATE runs SET state = 'failed', current_stage = 'transcribing', "
                "error_code = 'asr.not_configured', "
                "error_message = '转写组件尚未配置，请稍后重试' WHERE item_id = :item_id"
            ),
            {"item_id": item_id},
        )
        session.commit()
    _seed_transcript(host, item_id)
    token = host.client.cookies.get("trove_session")
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, color_scheme="dark"
    )
    context.add_cookies(
        [{"name": "trove_session", "value": token, "url": host.base_url}]
    )
    page = context.new_page()
    page.goto(f"{host.base_url}/items/{item_id}/listen", wait_until="domcontentloaded")
    assert page.locator(".now-playing").is_visible()
    assert page.locator(".status-panel").count() == 1
    colors = page.locator(".now-playing").evaluate(
        "(e) => { const s = getComputedStyle(e);"
        " return { background: s.backgroundColor, color: s.color }; }"
    )
    assert colors["background"] == "rgb(23, 22, 20)"
    assert colors["color"] == "rgb(244, 239, 230)"
    heading = page.locator(".now-title").evaluate(
        "(e) => { const s = getComputedStyle(e); return s.color; }"
    )
    assert heading == "rgb(244, 239, 230)"
    note = page.locator(".now-missing .status-message").evaluate(
        "(e) => { const s = getComputedStyle(e); return s.color; }"
    )
    assert note == "rgba(244, 239, 230, 0.72)"
    retry = page.locator(".now-missing .status-actions button").evaluate(
        "(e) => { const s = getComputedStyle(e);"
        " return { color: s.color, background: s.backgroundColor }; }"
    )
    assert retry["color"] == "rgb(244, 239, 230)"
    assert retry["background"] != "rgba(0, 0, 0, 0)"
    transcript = page.locator(".transcript-heading").evaluate(
        "(e) => { const s = getComputedStyle(e); return s.color; }"
    )
    assert transcript == "rgb(244, 239, 230)"
    context.close()


def _circle_and_icon_center(page, selector):
    return page.locator(selector).first.evaluate(
        """(e) => {
            const box = e.getBoundingClientRect();
            const icon = e.querySelector('span') || e;
            const glyph = icon.getBoundingClientRect();
            return {
                width: box.width,
                height: box.height,
                padding: getComputedStyle(e).padding,
                offsetX: Math.abs((box.x + box.width / 2) - (glyph.x + glyph.width / 2)),
                offsetY: Math.abs((box.y + box.height / 2) - (glyph.y + glyph.height / 2)),
            };
        }"""
    )


def test_round_player_buttons_stay_circular_and_centered(host, browser):
    bundle = seed_item(host, title="按钮几何", duration=20.0, audio_fixture="long.m4a")
    context = _context(browser, host)
    page = context.new_page()
    page.goto(f"{host.base_url}/library", wait_until="domcontentloaded")
    play = _circle_and_icon_center(page, ".play-button")
    assert play["width"] == play["height"] == 36
    assert play["padding"] == "0px"
    assert play["offsetX"] < 1 and play["offsetY"] < 1

    page.click(f'[data-play-item][data-item-id="{bundle.item.id}"]')
    page.wait_for_selector(f'[data-inline-for="{bundle.item.id}"]', state="visible")
    inline_play = _circle_and_icon_center(
        page, f'[data-inline-for="{bundle.item.id}"] .round-button'
    )
    assert inline_play["width"] == inline_play["height"] == 38
    assert inline_play["offsetX"] < 1 and inline_play["offsetY"] < 1

    page.goto(f"{host.base_url}/items/{bundle.item.id}/listen", wait_until="domcontentloaded")
    now_play = _circle_and_icon_center(page, ".now-play")
    assert now_play["width"] == now_play["height"] == 62
    assert now_play["offsetX"] < 1 and now_play["offsetY"] < 1
    speed = _circle_and_icon_center(page, ".now-controls .round-button")
    assert speed["width"] == speed["height"] == 38
    assert speed["offsetX"] < 1 and speed["offsetY"] < 1
    context.close()


_CONTRAST_AUDIT_JS = """
() => {
  const parse = (value) => {
    const match = value.match(/rgba?\\(([^)]+)\\)/);
    if (!match) return [0, 0, 0, 0];
    const parts = match[1].split(',').map((part) => parseFloat(part.trim()));
    return [parts[0] || 0, parts[1] || 0, parts[2] || 0, parts.length > 3 ? parts[3] : 1];
  };
  const over = (fg, bg) => {
    const alpha = fg[3] + bg[3] * (1 - fg[3]);
    if (!alpha) return [0, 0, 0, 0];
    return [
      (fg[0] * fg[3] + bg[0] * bg[3] * (1 - fg[3])) / alpha,
      (fg[1] * fg[3] + bg[1] * bg[3] * (1 - fg[3])) / alpha,
      (fg[2] * fg[3] + bg[2] * bg[3] * (1 - fg[3])) / alpha,
      alpha,
    ];
  };
  const luminance = (color) => {
    const values = color.slice(0, 3).map((value) => {
      const channel = value / 255;
      return channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
  };
  const contrast = (a, b) => {
    const first = luminance(a);
    const second = luminance(b);
    return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
  };
  const effectiveBackground = (element) => {
    const chain = [];
    let node = element;
    while (node && node.nodeType === 1) {
      chain.push(node);
      node = node.parentElement;
    }
    chain.reverse();
    let background = [255, 255, 255, 1];
    for (const ancestor of chain) {
      const color = parse(getComputedStyle(ancestor).backgroundColor);
      if (color[3] > 0) background = over(color, background);
    }
    return background;
  };
  const failures = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const text = walker.currentNode.textContent.trim();
    if (!text) continue;
    const element = walker.currentNode.parentElement;
    if (!element || seen.has(element) || element.closest('.cover')) continue;
    seen.add(element);
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1 || style.visibility === 'hidden') continue;
    if (parseFloat(style.opacity) === 0) continue;
    const background = effectiveBackground(element);
    const foreground = over(parse(style.color), background);
    const ratio = contrast(foreground, background);
    const size = parseFloat(style.fontSize);
    const weight = parseInt(style.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    if (ratio < (large ? 3 : 4.5)) {
      failures.push({
        text: text.slice(0, 50),
        tag: element.tagName.toLowerCase(),
        className: String(element.className || ''),
        ratio: Math.round(ratio * 100) / 100,
        color: style.color,
        background: `rgba(${background.map((value) => Math.round(value)).join(',')})`,
      });
    }
  }
  return failures;
}
"""


def _contrast_failures(page):
    page.evaluate("document.querySelectorAll('details').forEach((details) => details.open = true)")
    return page.evaluate(_CONTRAST_AUDIT_JS)


def test_all_pages_pass_contrast_audit_in_light_and_dark(host, browser):
    from sqlalchemy import text

    failed = seed_item(
        host,
        title="失败的记忆播客",
        author="张三",
        tags=["记忆", "智能体"],
        duration=20.0,
        audio_fixture="long.m4a",
        run_state="failed",
    )
    with host.runtime.sessions() as session:
        session.execute(
            text(
                "UPDATE runs SET error_code = 'asr.not_configured', "
                "error_message = '转写组件尚未配置，请稍后重试', "
                "current_stage = 'transcribing' WHERE item_id = :item_id"
            ),
            {"item_id": failed.item.id},
        )
        session.commit()
    _seed_transcript(host, failed.item.id)
    ready = seed_item(
        host,
        title="已经完成的内容",
        author="李四",
        source_key="seed:contrast-ready",
        tags=["注意力"],
        consumption_state="in_progress",
        position=1.0,
    )
    for item in (failed, ready):
        host.runtime.search_index.index_item(item.item.id)

    host.login()
    token = host.client.cookies.get("trove_session")
    pages = (
        "/library",
        "/add",
        "/search?q=记忆",
        f"/items/{failed.item.id}",
        f"/items/{ready.item.id}",
        f"/items/{failed.item.id}/listen",
        f"/items/{ready.item.id}/listen",
    )
    for color_scheme in ("light", "dark"):
        context = browser.new_context(
            viewport={"width": 1280, "height": 1000}, color_scheme=color_scheme
        )
        context.add_cookies(
            [{"name": "trove_session", "value": token, "url": host.base_url}]
        )
        page = context.new_page()
        for path in pages:
            page.goto(f"{host.base_url}{path}", wait_until="domcontentloaded")
            failures = _contrast_failures(page)
            assert failures == [], f"{color_scheme} contrast failures on {path}: {failures}"
        context.close()

    for color_scheme in ("light", "dark"):
        context = browser.new_context(
            viewport={"width": 1280, "height": 1000}, color_scheme=color_scheme
        )
        page = context.new_page()
        page.goto(f"{host.base_url}/login", wait_until="domcontentloaded")
        failures = _contrast_failures(page)
        assert failures == [], f"{color_scheme} contrast failures on /login: {failures}"
        context.close()
